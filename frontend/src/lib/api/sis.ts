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
  institution_email: string | null
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
  institution_email: string | null
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
  faculty_code: string | null
  designation: string | null
  specialization: string | null
  primary_department: { id: string; name: string; code: string } | null
  photo_url: string | null
  /** Active responsibility grants (GUIDE / EVALUATOR / BOARD / DEAN). */
  responsibilities: string[]
  is_active: boolean
}

export interface FacultyDetailOut extends FacultyDirectoryItem {
  identifier: string | null
  institution_email: string | null
  qualifications: string | null
  bio: string | null
  office_location: string | null
  phone: string | null
  joining_date: string | null
  active_assignments: {
    course: { id: string; name: string; code: string }
    semester_label: string
    section: { id: string; name: string } | null
    role: string
  }[]
  /** Programs this faculty member is assigned to teach. */
  teaching_programs: { id: string; name: string; code: string; degree_type: string }[]
  /** Programs this DEAN governs (empty for non-DEAN users). */
  governing_programs: { id: string; name: string; code: string; degree_type: string }[]
  profile_created_at: string | null
  profile_updated_at: string | null
}

// Governance Directory (P1.9A)
export interface GovernanceDeptInfo {
  id: string
  name: string
  code: string
}

export interface GovernanceDeanItem {
  user_id: string
  full_name: string
  email: string
  designation: string | null
  department: GovernanceDeptInfo | null
  responsibilities: string[]
  is_active: boolean
}

export interface GovernanceBoardItem {
  user_id: string
  full_name: string
  email: string
  designation: string | null
  department: GovernanceDeptInfo | null
  is_active: boolean
}

export interface GovernanceDeanListResponse {
  total: number
  items: GovernanceDeanItem[]
}

export interface GovernanceBoardListResponse {
  total: number
  items: GovernanceBoardItem[]
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
// Import Batches (H64.1)
// ---------------------------------------------------------------------------

export interface ImportBatch {
  id:             string
  batch_ref:      string
  imported_by:    string
  imported_at:    string
  record_type:    string
  total_records:  number
  success_count:  number
  failed_count:   number
  is_rolled_back: boolean
  rolled_back_by: string | null
  rolled_back_at: string | null
  // P1.4 academic context (null for older batches)
  program_id:    string | null
  program_name:  string | null
  batch_id:      string | null
  batch_name:    string | null
  semester_id:   string | null
  semester_name: string | null
  section_id:    string | null
  section_name:  string | null
}

export interface ImportBatchListOut {
  items: ImportBatch[]
  total: number
}

// ---------------------------------------------------------------------------
// Student Lifecycle (H64.3)
// ---------------------------------------------------------------------------

export interface LifecycleHistoryEntry {
  id:          string
  from_status: string | null
  to_status:   string
  reason:      string | null
  changed_by:  string
  changed_at:  string
}

export interface LifecycleStatusOut {
  student_id:     string
  current_status: string
  allowed_next:   string[]
  history:        LifecycleHistoryEntry[]
}

export interface LifecycleTransitionOut {
  student_id:      string
  previous_status: string
  new_status:      string
  is_active:       boolean
  message:         string
}

export interface FacultyLifecycleStatusOut {
  faculty_id:     string
  current_status: string
  allowed_next:   string[]
  history:        LifecycleHistoryEntry[]
}

export interface FacultyLifecycleTransitionOut {
  faculty_id:      string
  previous_status: string
  new_status:      string
  is_active:       boolean
  message:         string
}

// ---------------------------------------------------------------------------
// Bulk Operations (H64.5)
// ---------------------------------------------------------------------------

export interface BulkOpResult {
  action:    string
  requested: number
  succeeded: number
  failed:    number
  errors:    string[]
}

// ---------------------------------------------------------------------------
// Validation Report (H64.8)
// ---------------------------------------------------------------------------

export interface ValidationItem { id: string; detail: string }
export type ValidationSeverity = 'ERROR' | 'WARNING' | 'INFO'

export interface CheckResult {
  check_id:    string
  label:       string
  description: string
  severity:    ValidationSeverity
  count:       number
  items:       ValidationItem[]
}

export interface ValidationReportOut {
  generated_at: string
  total_issues: number
  checks:       CheckResult[]
}

// ---------------------------------------------------------------------------
// Global Search (H64.7)
// ---------------------------------------------------------------------------

export interface StudentHit  { id: string; full_name: string; email: string; usn: string | null; is_active: boolean }
export interface FacultyHit  { id: string; full_name: string; email: string; employee_id: string | null; is_active: boolean }
export interface SectionHit  { id: string; name: string; is_active: boolean }
export interface CourseHit   { id: string; code: string; title: string }
export interface SearchResultsOut {
  query:    string
  students: StudentHit[]
  faculty:  FacultyHit[]
  sections: SectionHit[]
  courses:  CourseHit[]
}

// ---------------------------------------------------------------------------
// Enrollment Capacity (H64.6)
// ---------------------------------------------------------------------------

export type CapacityStatus = 'HEALTHY' | 'NEAR_FULL' | 'FULL' | 'OVER' | 'NO_CAP'

export interface SectionCapacityOut {
  section_id:   string
  section_name: string
  semester_id:  string
  max_strength: number | null
  enrolled:     number
  available:    number | null
  is_full:      boolean
  fill_pct:     number | null
  // P1.2 Task A — academic-hierarchy context
  school_id:        string | null
  school_name:      string | null
  department_id:    string | null
  department_name:  string | null
  program_id:       string | null
  program_name:     string | null
  program_code:     string | null
  batch_id:         string | null
  batch_name:       string | null
  semester_number:  number | null
  semester_label:   string | null
  status:           CapacityStatus
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
  status:     'PRESENT' | 'ABSENT'
  remarks?:   string
}

export interface AttendanceMarkIn {
  records:      AttendanceMarkEntry[]
  edit_reason?: string
}

export interface AttendanceRecordEditIn {
  status:       'PRESENT' | 'ABSENT'
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
  status:        'PRESENT' | 'ABSENT'
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
  status:         'PRESENT' | 'ABSENT'
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

  // Import history (H64.1)
  listImportBatches: (limit = 50, offset = 0): Promise<ImportBatchListOut> =>
    api.get<ImportBatchListOut>('/sis/imports', { params: { limit, offset } }).then(r => r.data),

  getImportBatch: (batchId: string): Promise<ImportBatch> =>
    api.get<ImportBatch>(`/sis/imports/${batchId}`).then(r => r.data),

  // Import rollback (H64.2)
  rollbackImportBatch: (batchId: string): Promise<{ batch_id: string; batch_ref: string; rolled_back_at: string; message: string }> =>
    api.post(`/sis/imports/${batchId}/rollback`).then(r => r.data),

  // Student lifecycle (H64.3)
  getStudentLifecycle: (studentId: string): Promise<LifecycleStatusOut> =>
    api.get<LifecycleStatusOut>(`/sis/students/${studentId}/lifecycle`).then(r => r.data),

  transitionStudentLifecycle: (studentId: string, newStatus: string, reason?: string): Promise<LifecycleTransitionOut> =>
    api.post<LifecycleTransitionOut>(`/sis/students/${studentId}/lifecycle`, { new_status: newStatus, reason: reason ?? null }).then(r => r.data),

  // Bulk operations (H64.5)
  bulkStudentAction: (studentIds: string[], action: 'DEACTIVATE' | 'ARCHIVE', reason?: string): Promise<BulkOpResult> =>
    api.post<BulkOpResult>('/sis/students/bulk', { student_ids: studentIds, action, reason: reason ?? null }).then(r => r.data),

  bulkFacultyAction: (facultyIds: string[], action: 'DEACTIVATE' | 'ARCHIVE', reason?: string): Promise<BulkOpResult> =>
    api.post<BulkOpResult>('/sis/faculty/bulk', { faculty_ids: facultyIds, action, reason: reason ?? null }).then(r => r.data),

  // Enrollment capacity (H64.6)
  listSectionsCapacity: (semesterId?: string): Promise<SectionCapacityOut[]> =>
    api.get<SectionCapacityOut[]>('/sis/capacity/sections', { params: semesterId ? { semester_id: semesterId } : {} }).then(r => r.data),

  getSectionCapacity: (sectionId: string): Promise<SectionCapacityOut> =>
    api.get<SectionCapacityOut>(`/sis/sections/${sectionId}/capacity`).then(r => r.data),

  setSectionCapacity: (sectionId: string, maxStrength: number | null): Promise<SectionCapacityOut> =>
    api.put<SectionCapacityOut>(`/sis/sections/${sectionId}/capacity`, { max_strength: maxStrength }).then(r => r.data),

  // Validation report (H64.8)
  getValidationReport: (): Promise<ValidationReportOut> =>
    api.get<ValidationReportOut>('/sis/validation/report').then(r => r.data),

  // Global search (H64.7)
  search: (q: string): Promise<SearchResultsOut> =>
    api.get<SearchResultsOut>('/sis/search', { params: { q } }).then(r => r.data),

  // Faculty lifecycle (H64.4)
  getFacultyLifecycle: (facultyId: string): Promise<FacultyLifecycleStatusOut> =>
    api.get<FacultyLifecycleStatusOut>(`/sis/faculty/${facultyId}/lifecycle`).then(r => r.data),

  transitionFacultyLifecycle: (facultyId: string, newStatus: string, reason?: string): Promise<FacultyLifecycleTransitionOut> =>
    api.post<FacultyLifecycleTransitionOut>(`/sis/faculty/${facultyId}/lifecycle`, { new_status: newStatus, reason: reason ?? null }).then(r => r.data),

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

  // ---------------------------------------------------------------------------
  // Internal Marks (H57)
  // ---------------------------------------------------------------------------

  listComponentTemplates: (): Promise<ComponentTemplate[]> =>
    api.get<ComponentTemplate[]>('/sis/marks/component-templates').then(r => r.data),

  createMarksComponent: (body: ComponentCreateIn): Promise<MarksComponent> =>
    api.post<MarksComponent>('/sis/marks/components', body).then(r => r.data),

  listMarksComponents: (params: {
    course_id?: string; section_id?: string; semester_id?: string; status?: string
  } = {}): Promise<MarksComponent[]> =>
    api.get<MarksComponent[]>('/sis/marks/components', { params }).then(r => r.data),

  getMarksComponent: (componentId: string): Promise<MarksComponent> =>
    api.get<MarksComponent>(`/sis/marks/components/${componentId}`).then(r => r.data),

  updateMarksComponent: (componentId: string, body: Partial<ComponentCreateIn>): Promise<MarksComponent> =>
    api.put<MarksComponent>(`/sis/marks/components/${componentId}`, body).then(r => r.data),

  deleteMarksComponent: (componentId: string): Promise<void> =>
    api.delete(`/sis/marks/components/${componentId}`).then(r => r.data),

  publishMarksComponent: (componentId: string): Promise<MarksComponent> =>
    api.post<MarksComponent>(`/sis/marks/components/${componentId}/publish`).then(r => r.data),

  lockMarksComponent: (componentId: string): Promise<MarksComponent> =>
    api.post<MarksComponent>(`/sis/marks/components/${componentId}/lock`).then(r => r.data),

  reopenMarksComponent: (componentId: string, reason: string): Promise<MarksComponent> =>
    api.post<MarksComponent>(`/sis/marks/components/${componentId}/reopen`, { reason }).then(r => r.data),

  getMarksEntries: (componentId: string): Promise<MarkEntryOut[]> =>
    api.get<MarkEntryOut[]>(`/sis/marks/components/${componentId}/entries`).then(r => r.data),

  bulkEnterMarks: (componentId: string, body: BulkMarkEntryIn): Promise<BulkMarkEntryResult> =>
    api.post<BulkMarkEntryResult>(`/sis/marks/components/${componentId}/entries/bulk`, body).then(r => r.data),

  editMarkEntry: (componentId: string, entryId: string, body: SingleMarkEditIn): Promise<MarkEntryOut> =>
    api.patch<MarkEntryOut>(`/sis/marks/components/${componentId}/entries/${entryId}`, body).then(r => r.data),

  downloadMarksTemplate: (componentId: string): Promise<void> =>
    api.get(`/sis/marks/components/${componentId}/entries/template.xlsx`, { responseType: 'blob' }).then(r => {
      _triggerSisDownload(
        r.data,
        `marks_template.xlsx`,
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
      )
    }),

  previewMarksImport: (componentId: string, file: File): Promise<MarksImportPreviewOut> => {
    const form = new FormData()
    form.append('file', file)
    return api.post<MarksImportPreviewOut>(
      `/sis/marks/components/${componentId}/entries/import/preview`,
      form,
      { headers: { 'Content-Type': 'multipart/form-data' } },
    ).then(r => r.data)
  },

  commitMarksImport: (componentId: string, file: File, editReason?: string): Promise<MarksImportCommitResult> => {
    const form = new FormData()
    form.append('file', file)
    const params: Record<string, string> = {}
    if (editReason) params.edit_reason = editReason
    return api.post<MarksImportCommitResult>(
      `/sis/marks/components/${componentId}/entries/import/commit`,
      form,
      { headers: { 'Content-Type': 'multipart/form-data' }, params },
    ).then(r => r.data)
  },

  getSectionMarksReport: (sectionId: string, courseId?: string): Promise<SectionMarksReportOut> =>
    api.get<SectionMarksReportOut>(`/sis/marks/analytics/section/${sectionId}`, {
      params: courseId ? { course_id: courseId } : {},
    }).then(r => r.data),

  getSectionReadiness: (sectionId: string, threshold?: number): Promise<SectionReadinessOut> =>
    api.get<SectionReadinessOut>(`/sis/marks/readiness/section/${sectionId}`, {
      params: threshold !== undefined ? { threshold } : {},
    }).then(r => r.data),

  getMyCoursesOverview: (): Promise<FacultyCourseComponentSummary[]> =>
    api.get<FacultyCourseComponentSummary[]>('/sis/marks/my-courses').then(r => r.data),

  getMyMarks: (): Promise<MyMarksOut> =>
    api.get<MyMarksOut>('/sis/marks/me').then(r => r.data),

  // ── My Subjects / Subject Details (Phase 2 — student subject hub) ───────────

  getMySubjects: (semesterId?: string): Promise<MySubjectsOut> =>
    api.get<MySubjectsOut>('/sis/me/subjects', {
      params: semesterId ? { semester_id: semesterId } : {},
    }).then(r => r.data),

  getSubjectDetail: (courseId: string): Promise<SubjectDetailOut> =>
    api.get<SubjectDetailOut>(`/sis/me/subjects/${courseId}`).then(r => r.data),

  // ── H60 Results Management ──────────────────────────────────────────────────

  createDeclaration: (body: {
    exam_session_id: string
    semester_id: string
    grading_policy_id: string
    declaration_type?: string
    title?: string
    notes?: string
    internal_marks_required?: boolean
  }): Promise<ResultDeclarationOut> =>
    api.post<ResultDeclarationOut>('/sis/results/declarations', body).then(r => r.data),

  listGradingPolicies: (): Promise<GradingPolicyListOut[]> =>
    api.get<GradingPolicyListOut[]>('/sis/results/grading-policies').then(r => r.data),

  listDeclarations: (params?: { semester_id?: string; status?: string; declaration_type?: string }): Promise<ResultDeclarationListOut[]> =>
    api.get<ResultDeclarationListOut[]>('/sis/results/declarations', { params }).then(r => r.data),

  getDeclaration: (id: string): Promise<ResultDeclarationOut> =>
    api.get<ResultDeclarationOut>(`/sis/results/declarations/${id}`).then(r => r.data),

  getComputationStatus: (id: string): Promise<ComputationStatusOut> =>
    api.get<ComputationStatusOut>(`/sis/results/declarations/${id}/computation-status`).then(r => r.data),

  computeResults: (id: string, force = false): Promise<ComputeResultOut> =>
    api.post<ComputeResultOut>(`/sis/results/declarations/${id}/compute`, { force }).then(r => r.data),

  computeSgpaCgpa: (id: string): Promise<SemesterResultOut[]> =>
    api.post<SemesterResultOut[]>(`/sis/results/declarations/${id}/compute-sgpa-cgpa`).then(r => r.data),

  computeRanks: (id: string): Promise<SemesterResultOut[]> =>
    api.post<SemesterResultOut[]>(`/sis/results/declarations/${id}/compute-ranks`).then(r => r.data),

  verifyDeclaration: (id: string): Promise<ResultDeclarationOut> =>
    api.post<ResultDeclarationOut>(`/sis/results/declarations/${id}/verify`).then(r => r.data),

  publishDeclaration: (id: string): Promise<ResultDeclarationOut> =>
    api.post<ResultDeclarationOut>(`/sis/results/declarations/${id}/publish`).then(r => r.data),

  lockDeclaration: (id: string): Promise<ResultDeclarationOut> =>
    api.post<ResultDeclarationOut>(`/sis/results/declarations/${id}/lock`).then(r => r.data),

  revertToDraft: (id: string, reason: string): Promise<ResultDeclarationOut> =>
    api.post<ResultDeclarationOut>(`/sis/results/declarations/${id}/revert-to-draft`, { reason }).then(r => r.data),

  listGradeCards: (id: string, params?: { section_id?: string }): Promise<GradeCardOut[]> =>
    api.get<GradeCardOut[]>(`/sis/results/declarations/${id}/grade-cards`, { params }).then(r => r.data),

  getGradeCard: (declId: string, studentId: string): Promise<GradeCardOut> =>
    api.get<GradeCardOut>(`/sis/results/declarations/${declId}/grade-cards/${studentId}`).then(r => r.data),

  getRankList: (id: string, scope = 'program'): Promise<RankListOut> =>
    api.get<RankListOut>(`/sis/results/declarations/${id}/rank-list`, { params: { scope } }).then(r => r.data),

  listGraceMarks: (id: string): Promise<GraceMarkLogOut[]> =>
    api.get<GraceMarkLogOut[]>(`/sis/results/declarations/${id}/grace-marks`).then(r => r.data),

  applyGraceMark: (id: string, body: { student_id: string; course_id: string; grace_marks_applied: number; reason: string }): Promise<GraceMarkLogOut> =>
    api.post<GraceMarkLogOut>(`/sis/results/declarations/${id}/grace-marks`, body).then(r => r.data),

  revokeGraceMark: (declId: string, logId: string, revoke_reason: string): Promise<void> =>
    api.delete(`/sis/results/declarations/${declId}/grace-marks/${logId}`, { data: { revoke_reason } }).then(() => {}),

  getMyResults: (): Promise<SemesterResultOut[]> =>
    api.get<SemesterResultOut[]>('/sis/results/my-results').then(r => r.data),

  getMyGradeCard: (declId: string): Promise<GradeCardOut> =>
    api.get<GradeCardOut>(`/sis/results/my-grade-card/${declId}`).then(r => r.data),

  getMyTranscript: (): Promise<TranscriptOut> =>
    api.get<TranscriptOut>('/sis/results/my-transcript').then(r => r.data),

  getStudentTranscript: (studentId: string): Promise<TranscriptOut> =>
    api.get<TranscriptOut>(`/sis/results/students/${studentId}/transcript`).then(r => r.data),

  // ── H58 Hall Tickets ────────────────────────────────────────────────────────

  computeEligibility: (body: { semester_id: string; section_id?: string; threshold_pct?: number }): Promise<EligibilityComputeResult> =>
    api.post<EligibilityComputeResult>('/sis/hall-tickets/eligibility/compute', body).then(r => r.data),

  publishEligibility: (body: { semester_id: string; section_id?: string }): Promise<EligibilityPublishResult> =>
    api.post<EligibilityPublishResult>('/sis/hall-tickets/eligibility/publish', body).then(r => r.data),

  getEligibilityDashboard: (params: {
    semester_id: string
    section_id?: string
    status?: string
    publish_status?: string
    has_shortage?: boolean
  }): Promise<EligibilityDashboardOut> =>
    api.get<EligibilityDashboardOut>('/sis/hall-tickets/eligibility', { params }).then(r => r.data),

  getEligibility: (eligibilityId: string): Promise<EligibilityOut> =>
    api.get<EligibilityOut>(`/sis/hall-tickets/eligibility/${eligibilityId}`).then(r => r.data),

  overrideEligibility: (eligibilityId: string, body: { status: string; reason: string }): Promise<EligibilityOut> =>
    api.post<EligibilityOut>(`/sis/hall-tickets/eligibility/${eligibilityId}/override`, body).then(r => r.data),

  generateHallTicketBatch: (body: { semester_id: string; section_id?: string; notes?: string }): Promise<HallTicketBatchOut> =>
    api.post<HallTicketBatchOut>('/sis/hall-tickets/batches', body).then(r => r.data),

  listHallTicketBatches: (semester_id?: string): Promise<HallTicketBatchOut[]> =>
    api.get<HallTicketBatchOut[]>('/sis/hall-tickets/batches', { params: semester_id ? { semester_id } : {} }).then(r => r.data),

  getHallTicket: (eligibilityId: string): Promise<HallTicketOut> =>
    api.get<HallTicketOut>(`/sis/hall-tickets/ticket/${eligibilityId}`).then(r => r.data),

  getMyEligibility: (semester_id: string): Promise<MyEligibilityOut> =>
    api.get<MyEligibilityOut>('/sis/hall-tickets/my-eligibility', { params: { semester_id } }).then(r => r.data),

  getMyHallTicket: (session_id: string): Promise<MyHallTicketExamOut> =>
    api.get<MyHallTicketExamOut>('/sis/exam/my-hall-ticket', { params: { session_id } }).then(r => r.data),

  // ── H59 Exam Management ─────────────────────────────────────────────────────

  listExamCenters: (include_inactive = false): Promise<ExamCenterOut[]> =>
    api.get<ExamCenterOut[]>('/sis/exam/centers', { params: { include_inactive } }).then(r => r.data),

  createExamCenter: (body: { center_code: string; center_name: string; address?: string; capacity?: number; is_internal?: boolean }): Promise<ExamCenterOut> =>
    api.post<ExamCenterOut>('/sis/exam/centers', body).then(r => r.data),

  updateExamCenter: (centerId: string, body: Partial<{ center_name: string; address: string; capacity: number; is_internal: boolean; is_active: boolean }>): Promise<ExamCenterOut> =>
    api.put<ExamCenterOut>(`/sis/exam/centers/${centerId}`, body).then(r => r.data),

  listExamSessions: (params: { semester_id?: string; status?: string; session_type?: string } = {}): Promise<ExamSessionOut[]> =>
    api.get<ExamSessionOut[]>('/sis/exam/sessions', { params }).then(r => r.data),

  createExamSession: (body: {
    semester_id: string; session_type: string; session_name: string
    academic_year: string; start_date: string; end_date: string; notes?: string
  }): Promise<ExamSessionOut> =>
    api.post<ExamSessionOut>('/sis/exam/sessions', body).then(r => r.data),

  getExamSession: (sessionId: string): Promise<ExamSessionOut> =>
    api.get<ExamSessionOut>(`/sis/exam/sessions/${sessionId}`).then(r => r.data),

  updateExamSession: (sessionId: string, body: { session_name?: string; academic_year?: string; start_date?: string; end_date?: string; notes?: string }): Promise<ExamSessionOut> =>
    api.put<ExamSessionOut>(`/sis/exam/sessions/${sessionId}`, body).then(r => r.data),

  deleteExamSession: (sessionId: string): Promise<void> =>
    api.delete(`/sis/exam/sessions/${sessionId}`).then(() => {}),

  publishExamSession: (sessionId: string): Promise<ExamSessionOut> =>
    api.post<ExamSessionOut>(`/sis/exam/sessions/${sessionId}/publish`).then(r => r.data),

  lockExamSession: (sessionId: string): Promise<ExamSessionOut> =>
    api.post<ExamSessionOut>(`/sis/exam/sessions/${sessionId}/lock`).then(r => r.data),

  completeExamSession: (sessionId: string): Promise<ExamSessionOut> =>
    api.post<ExamSessionOut>(`/sis/exam/sessions/${sessionId}/complete`).then(r => r.data),

  listExamSchedules: (sessionId: string, section_id?: string): Promise<ExamScheduleOut[]> =>
    api.get<ExamScheduleOut[]>(`/sis/exam/sessions/${sessionId}/schedules`, { params: section_id ? { section_id } : {} }).then(r => r.data),

  createExamSchedule: (sessionId: string, body: {
    course_id: string; section_id: string; exam_date: string
    start_time: string; end_time: string; center_id?: string; room_number?: string; notes?: string
  }): Promise<ExamScheduleOut> =>
    api.post<ExamScheduleOut>(`/sis/exam/sessions/${sessionId}/schedules`, body).then(r => r.data),

  updateExamSchedule: (scheduleId: string, body: { exam_date?: string; start_time?: string; end_time?: string; center_id?: string; room_number?: string; notes?: string }): Promise<ExamScheduleOut> =>
    api.put<ExamScheduleOut>(`/sis/exam/schedules/${scheduleId}`, body).then(r => r.data),

  deleteExamSchedule: (scheduleId: string): Promise<void> =>
    api.delete(`/sis/exam/schedules/${scheduleId}`).then(() => {}),

  listInvigilation: (sessionId: string): Promise<InvigilationOut[]> =>
    api.get<InvigilationOut[]>(`/sis/exam/sessions/${sessionId}/invigilation`).then(r => r.data),

  assignInvigilation: (sessionId: string, body: { faculty_user_id: string; schedule_id?: string; center_id?: string; room_number?: string; notes?: string }): Promise<InvigilationOut> =>
    api.post<InvigilationOut>(`/sis/exam/sessions/${sessionId}/invigilation`, body).then(r => r.data),

  deleteInvigilation: (invigilationId: string): Promise<void> =>
    api.delete(`/sis/exam/invigilation/${invigilationId}`).then(() => {}),

  allocateSeats: (sessionId: string, body: { center_id: string; rooms: { room_number: string; capacity: number }[]; section_id?: string }): Promise<SeatingAllocationResult> =>
    api.post<SeatingAllocationResult>(`/sis/exam/sessions/${sessionId}/allocate-seats`, body).then(r => r.data),

  listSeating: (sessionId: string, section_id?: string): Promise<StudentSeatOut[]> =>
    api.get<StudentSeatOut[]>(`/sis/exam/sessions/${sessionId}/seating`, { params: section_id ? { section_id } : {} }).then(r => r.data),

  getMyTimetable: (session_id: string): Promise<StudentTimetableOut> =>
    api.get<StudentTimetableOut>('/sis/exam/my-timetable', { params: { session_id } }).then(r => r.data),

  // ---------------------------------------------------------------------------
  // Governance Directory (P1.9A) — Admin-only
  // ---------------------------------------------------------------------------

  listGovernanceDeans: (): Promise<GovernanceDeanListResponse> =>
    api.get<GovernanceDeanListResponse>('/sis/governance/deans').then(r => r.data),

  listGovernanceBoard: (): Promise<GovernanceBoardListResponse> =>
    api.get<GovernanceBoardListResponse>('/sis/governance/board').then(r => r.data),

  // ---------------------------------------------------------------------------
  // Dean department-scoped directory endpoints
  // ---------------------------------------------------------------------------

  listDeanFaculty: (params: {
    page?: number
    page_size?: number
    search?: string
    is_active?: boolean
  }): Promise<DirectoryPage<FacultyDirectoryItem>> =>
    api.get<DirectoryPage<FacultyDirectoryItem>>('/sis/dean/faculty', { params }).then(r => r.data),

  listDeanStudents: (params: {
    page?: number
    page_size?: number
    search?: string
    batch_id?: string
    section_id?: string
    is_active?: boolean
  }): Promise<DirectoryPage<StudentDirectoryItem>> =>
    api.get<DirectoryPage<StudentDirectoryItem>>('/sis/dean/students', { params }).then(r => r.data),
}

// ---------------------------------------------------------------------------
// H57 Internal Marks types
// ---------------------------------------------------------------------------

export interface ComponentTemplate {
  template_key: string
  component_type: string
  name: string
  max_marks: number
  display_order: number
}

export interface MarksComponent {
  id: string
  course_id: string
  course_code: string | null
  course_title: string | null
  section_id: string
  section_name: string | null
  semester_id: string
  created_by: string
  component_type: string
  name: string
  max_marks: number
  weightage: number | null
  due_date: string | null
  display_order: number | null
  status: 'DRAFT' | 'PUBLISHED' | 'LOCKED'
  published_at: string | null
  locked_at: string | null
  locked_by: string | null
  reopened_by: string | null
  reopened_at: string | null
  reopen_reason: string | null
  is_active: boolean
  entries_count: number
  filled_count: number
  created_at: string
  updated_at: string | null
}

export interface ComponentCreateIn {
  course_id: string
  section_id: string
  semester_id: string
  component_type: string
  name: string
  max_marks: number
  weightage?: number
  due_date?: string
  display_order?: number
}

export interface MarkEntryItem {
  student_id: string
  marks_obtained: number | null
  remarks?: string
}

export interface BulkMarkEntryIn {
  entries: MarkEntryItem[]
  edit_reason?: string
}

export interface SingleMarkEditIn {
  marks_obtained?: number | null
  remarks?: string
  edit_reason?: string
}

export interface MarkEntryOut {
  id: string
  component_id: string
  student_id: string
  student_name: string | null
  usn: string | null
  marks_obtained: number | null
  remarks: string | null
  marked_by: string | null
  marked_at: string | null
  edited_by: string | null
  edited_at: string | null
  edit_reason: string | null
  created_at: string
  updated_at: string | null
}

export interface BulkMarkEntryResult {
  component_id: string
  saved: number
  first_marks: number
  edits: number
}

export interface MarksImportRowResult {
  row_number: number
  student_name: string | null
  student_id: string | null
  usn: string | null
  email: string | null
  marks_obtained: number | null
  remarks: string | null
  is_valid: boolean
  errors: string[]
}

export interface MarksImportPreviewOut {
  component_id: string
  component_name: string
  max_marks: number
  total_rows: number
  valid_rows: number
  invalid_rows: number
  rows: MarksImportRowResult[]
}

export interface MarksImportCommitResult {
  component_id: string
  total: number
  saved: number
  skipped: number
  errors: string[]
}

export interface StudentComponentView {
  component_id: string
  component_type: string
  name: string
  max_marks: number
  weightage: number | null
  due_date: string | null
  display_order: number | null
  status: 'PUBLISHED' | 'LOCKED'
  marks_obtained: number | null
  remarks: string | null
}

export interface StudentCourseMarks {
  course_id: string
  course_code: string
  course_title: string
  section_id: string
  section_name: string
  total_marks_obtained: number | null
  total_max_marks: number | null
  components: StudentComponentView[]
}

export interface MyMarksOut {
  student_id: string
  student_name: string
  usn: string | null
  courses: StudentCourseMarks[]
}

// ---------------------------------------------------------------------------
// My Subjects / Subject Details (Phase 2 — student subject hub)
// ---------------------------------------------------------------------------

export interface MySubjectSummary {
  course_id: string
  course_code: string
  course_title: string
  credits: number
  semester: number
  course_type: string | null
  is_elective: boolean
  section_id: string
  section_name: string
  faculty_user_id: string | null
  faculty_name: string | null
  faculty_designation: string | null
  syllabus_id: string | null
  syllabus_status: string | null
}

export interface MySubjectsOut {
  student_id: string
  student_name: string
  usn: string | null
  semester_id: string | null
  subjects: MySubjectSummary[]
}

export interface SubjectFacultyInfo {
  user_id: string
  name: string
  designation: string | null
  email: string | null
  phone: string | null
  office_location: string | null
  photo_url: string | null
}

export interface SyllabusUnitOut {
  unit_number: number
  title: string
  hours: number | null
}

export interface SubjectCourseOutcomeOut {
  code: string
  description: string
  bloom_level: string | null
  display_order: number | null
}

export interface SubjectDetailOut {
  course_id: string
  course_code: string
  course_title: string
  credits: number
  semester: number
  course_type: string | null
  is_elective: boolean
  description: string | null
  hours_lecture: number | null
  hours_tutorial: number | null
  hours_practical: number | null
  section_id: string
  section_name: string
  faculty: SubjectFacultyInfo | null
  syllabus_id: string | null
  syllabus_version: number | null
  syllabus_status: string | null
  units: SyllabusUnitOut[]
  course_outcomes: SubjectCourseOutcomeOut[]
  internal_marks: StudentCourseMarks | null
}

export interface SectionStudentMarks {
  student_id: string
  student_name: string
  usn: string | null
  total_marks: number | null
  total_max: number | null
  fill_pct: number | null
}

export interface SectionMarksReportOut {
  section_id: string
  section_name: string
  course_id: string
  course_code: string
  course_title: string
  components: MarksComponent[]
  students: SectionStudentMarks[]
}

export interface FacultyCourseComponentSummary {
  course_id: string
  course_code: string
  course_title: string
  section_id: string
  section_name: string
  total_students: number
  components: MarksComponent[]
}

export interface StudentReadiness {
  student_id: string
  student_name: string
  usn: string | null
  attendance_ready: boolean
  internal_marks_ready: boolean
  attendance_pct: number | null
  marks_fill_pct: number | null
  notes: string[]
}

export interface SectionReadinessOut {
  section_id: string
  section_name: string
  course_id: string | null
  course_code: string | null
  total_students: number
  attendance_ready_count: number
  internal_marks_ready_count: number
  fully_ready_count: number
  students: StudentReadiness[]
}

// ---------------------------------------------------------------------------
// H60 Results Management types
// ---------------------------------------------------------------------------

export interface GradingPolicyListOut {
  id: string
  name: string
  program_id: string | null
  pass_percentage: number
  is_default: boolean
  is_active: boolean
  band_count: number
}

export interface ResultDeclarationListOut {
  id: string
  semester_id: string
  snapshot_academic_year: string
  snapshot_semester_name: string
  snapshot_grading_policy_name: string
  declaration_type: string
  title: string | null
  status: string
  published_at: string | null
  created_at: string
}

export interface ResultDeclarationOut {
  id: string
  exam_session_id: string
  semester_id: string
  snapshot_academic_year: string
  snapshot_semester_name: string
  snapshot_grading_policy_name: string
  declaration_type: string
  source_declaration_id: string | null
  grading_policy_id: string
  title: string | null
  notes: string | null
  internal_marks_required: boolean
  status: string
  verified_by: string | null
  verified_at: string | null
  published_by: string | null
  published_at: string | null
  locked_by: string | null
  locked_at: string | null
  created_by: string
  created_at: string
  updated_at: string | null
}

export interface ComputationStatusOut {
  declaration_id: string
  total_expected: number
  external_marks_entered: number
  external_marks_pending: number
  internal_marks_locked: boolean
  ready_to_compute: boolean
  blocking_reasons: string[]
}

export interface ComputeResultOut {
  declaration_id: string
  computed_count: number
  pass_count: number
  fail_count: number
  absent_count: number
  pending_count: number
  message: string
}

export interface GraceMarkLogOut {
  id: string
  declaration_id: string
  subject_result_id: string
  student_id: string
  course_id: string
  grace_marks_applied: number
  reason: string
  authorized_by: string
  authorized_at: string
  revoked_by: string | null
  revoked_at: string | null
  revoke_reason: string | null
  created_at: string
}

export interface GradeCardSubjectRow {
  course_id: string
  course_name: string
  course_code: string
  credits: number | null
  internal_marks: number | null
  external_marks: number | null
  grace_marks: number | null
  total_marks: number | null
  max_marks: number
  percentage: number | null
  grade_letter: string | null
  grade_point: number | null
  result_status: string
}

export interface GradeCardOut {
  student_id: string
  declaration_id: string
  snapshot_academic_year: string
  snapshot_semester_name: string
  snapshot_grading_policy_name: string
  declaration_type: string
  published_at: string | null
  sgpa: number | null
  cgpa: number | null
  total_credits_attempted: number | null
  total_credits_earned: number | null
  overall_result_status: string | null
  section_rank: number | null
  program_rank: number | null
  subjects: GradeCardSubjectRow[]
}

export interface RankEntryOut {
  rank: number
  student_id: string
  sgpa: number | null
  cgpa: number | null
  total_credits_earned: number | null
  overall_result_status: string | null
  section_rank: number | null
  program_rank: number | null
}

export interface RankListOut {
  declaration_id: string
  scope: string
  scope_ref_id: string | null
  total_students: number
  entries: RankEntryOut[]
}

export interface SemesterResultOut {
  id: string
  declaration_id: string
  student_id: string
  semester_id: string
  sgpa: number | null
  cgpa: number | null
  total_credits_attempted: number | null
  total_credits_earned: number | null
  overall_result_status: string | null
  section_rank: number | null
  program_rank: number | null
  computed_at: string | null
}

export interface TranscriptSemesterOut {
  declaration_id: string
  snapshot_academic_year: string
  snapshot_semester_name: string
  declaration_type: string
  published_at: string | null
  sgpa: number | null
  cgpa: number | null
  overall_result_status: string | null
  total_credits_attempted: number | null
  total_credits_earned: number | null
  subjects: GradeCardSubjectRow[]
}

export interface TranscriptOut {
  student_id: string
  cgpa: number | null
  total_credits: number | null
  semesters: TranscriptSemesterOut[]
}

function _triggerSisDownload(data: Blob, filename: string, mime: string) {
  const url = URL.createObjectURL(new Blob([data], { type: mime }))
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

// ── H58 Hall Ticket types ────────────────────────────────────────────────────

export interface EligibilityOut {
  id: string
  student_id: string
  student_name: string
  usn: string | null
  email: string
  semester_id: string
  publish_status: 'DRAFT' | 'PUBLISHED'
  status: 'ELIGIBLE' | 'NOT_ELIGIBLE' | 'CONDITIONAL'
  computed_at: string | null
  attendance_threshold_used: number
  computed_academic_year: string
  computed_semester_name: string
  attendance_pct: number | null
  has_shortage: boolean
  marks_all_locked: boolean
  marks_all_filled: boolean
  failure_reasons: string[]
  is_overridden: boolean
  override_by: string | null
  override_at: string | null
  override_reason: string | null
  override_status: string | null
  hall_ticket_number: string | null
  batch_id: string | null
  exam_session_id: string | null
  exam_schedule_id: string | null
  exam_center_id: string | null
  room_number: string | null
  seat_number: string | null
  created_at: string
  updated_at: string | null
}

export interface EligibilityDashboardOut {
  semester_id: string
  semester_name: string
  total_students: number
  eligible_count: number
  not_eligible_count: number
  conditional_count: number
  draft_count: number
  published_count: number
  rows: EligibilityOut[]
}

export interface EligibilityComputeResult {
  semester_id: string
  section_id: string | null
  threshold_pct: number
  processed: number
  eligible_count: number
  not_eligible_count: number
  skipped_overridden: number
}

export interface EligibilityPublishResult {
  semester_id: string
  published: number
  already_published: number
}

export interface HallTicketBatchOut {
  id: string
  semester_id: string
  semester_name: string | null
  scope: string
  scope_ref_id: string | null
  generated_by: string
  generated_at: string
  ticket_count: number
  ticket_prefix: string
  notes: string | null
  created_at: string
}

export interface HallTicketOut {
  hall_ticket_number: string
  student_id: string
  student_name: string
  usn: string | null
  semester_id: string
  semester_name: string
  academic_year: string
  status: string
  batch_id: string
  issued_at: string
  exam_session_id: string | null
  exam_schedule_id: string | null
  exam_center_id: string | null
  room_number: string | null
  seat_number: string | null
}

export interface MyEligibilityOut {
  student_id: string
  student_name: string
  usn: string | null
  semester_id: string
  semester_name: string
  status: 'ELIGIBLE' | 'NOT_ELIGIBLE' | 'CONDITIONAL'
  checklist: { check_name: string; passed: boolean; detail: string }[]
  failure_reasons: string[]
  hall_ticket_number: string | null
  is_ticket_available: boolean
}

// ── H59 Exam Management types ────────────────────────────────────────────────

export type ExamSessionStatus = 'DRAFT' | 'PUBLISHED' | 'SEATING_ALLOCATED' | 'LOCKED' | 'COMPLETED'
export type ExamSessionType = 'REGULAR' | 'SUPPLEMENTARY' | 'REVALUATION' | 'IMPROVEMENT'

export interface ExamCenterOut {
  id: string
  center_code: string
  center_name: string
  address: string | null
  capacity: number | null
  is_internal: boolean
  is_active: boolean
  created_at: string
  updated_at: string | null
}

export interface ExamSessionOut {
  id: string
  semester_id: string
  session_type: ExamSessionType
  session_name: string
  academic_year: string
  start_date: string
  end_date: string
  status: ExamSessionStatus
  notes: string | null
  source_exam_session_id: string | null
  attempt_number: number | null
  hall_ticket_generated_at: string | null
  hall_ticket_generated_by: string | null
  created_by: string
  created_at: string
  updated_at: string | null
  schedule_count: number
}

export interface ExamScheduleOut {
  id: string
  session_id: string
  course_id: string
  course_code: string
  course_title: string
  section_id: string
  section_name: string
  center_id: string | null
  center_name: string | null
  exam_date: string
  start_time: string
  end_time: string
  room_number: string | null
  notes: string | null
  created_by: string
  created_at: string
  updated_at: string | null
}

export interface InvigilationOut {
  id: string
  session_id: string
  schedule_id: string | null
  center_id: string | null
  center_name: string | null
  room_number: string | null
  faculty_user_id: string
  faculty_name: string | null
  assigned_by: string
  notes: string | null
  created_at: string
  exam_date: string | null
  start_time: string | null
  end_time: string | null
}

export interface SeatingAllocationResult {
  session_id: string
  allocated: number
  rooms_used: number
  total_capacity: number
  details: { room_number: string; capacity: number; assigned: number }[]
}

export interface StudentSeatOut {
  student_id: string
  student_name: string | null
  usn: string | null
  hall_ticket_number: string | null
  section_name: string | null
  center_name: string | null
  room_number: string | null
  seat_number: string | null
}

export interface CourseScheduleRow {
  course_id: string
  course_code: string
  course_title: string
  exam_date: string | null
  start_time: string | null
  end_time: string | null
  center_name: string | null
  room_number: string | null
  is_scheduled: boolean
}

export interface StudentTimetableOut {
  session_id: string
  session_name: string
  session_type: string
  semester_name: string
  seat: { center_name: string; address: string | null; room_number: string; seat_number: string } | null
  courses: CourseScheduleRow[]
}

export interface MyHallTicketExamOut {
  hall_ticket_number: string
  student_id: string
  student_name: string | null
  usn: string | null
  semester_name: string
  academic_year: string
  status: string
  seat: { center_name: string; address: string | null; room_number: string; seat_number: string } | null
  timetable: CourseScheduleRow[]
  issued_at: string | null
  exam_session_id: string | null
}
